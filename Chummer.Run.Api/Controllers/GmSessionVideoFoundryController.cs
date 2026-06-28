using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
public sealed class GmSessionVideoFoundryController : ControllerBase
{
    private const int MaxRequestBodyBytes = 16 * 1024;

    private readonly HubIdentityClient _identity;
    private readonly AccountService _accounts;
    private readonly GmSessionVideoFoundryService _foundry;

    public GmSessionVideoFoundryController(
        HubIdentityClient identity,
        AccountService accounts,
        GmSessionVideoFoundryService foundry)
    {
        _identity = identity;
        _accounts = accounts;
        _foundry = foundry;
    }

    [HttpGet("/gm/campaigns/{campaignId}/video-foundry")]
    [ProducesResponseType<GmSessionVideoFoundryHomeProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> Home([FromRoute] string campaignId, CancellationToken cancellationToken)
        => await WithUser(cancellationToken, userId => Ok(_foundry.GetHome(userId, campaignId)));

    [HttpGet("/gm/campaigns/{campaignId}/video-foundry/cast")]
    [ProducesResponseType<IReadOnlyList<FaceAssetProjection>>(StatusCodes.Status200OK)]
    public async Task<IActionResult> Cast([FromRoute] string campaignId, [FromQuery] string? q, CancellationToken cancellationToken)
        => await WithUser(cancellationToken, userId => Ok(_foundry.ListFaces(userId, campaignId, q)));

    [HttpPost("/gm/campaigns/{campaignId}/video-foundry/cast")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<FaceAssetProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> CreateCastFace(
        [FromRoute] string campaignId,
        [FromBody] CreateFaceAssetRequest? request,
        CancellationToken cancellationToken)
        => request is null
            ? BadRequest("face asset payload is required.")
            : await WithUser(cancellationToken, userId => Ok(_foundry.CreateFace(userId, campaignId, request)));

    [HttpGet("/gm/campaigns/{campaignId}/video-foundry/new")]
    [ProducesResponseType<object>(StatusCodes.Status200OK)]
    public async Task<IActionResult> NewVideoOptions([FromRoute] string campaignId, CancellationToken cancellationToken)
        => await WithUser(cancellationToken, userId =>
        {
            _ = _foundry.GetHome(userId, campaignId);
            return Ok(new
            {
                video_types = new[] { "player_teaser", "mr_johnson_briefing", "location_mood_clip", "newsreel", "faction_dispatch", "security_breach_report", "matrix_alert", "astral_disturbance_report", "post_session_recap" },
                audiences = new[] { "gm_only", "campaign_players", "selected_players", "faction_members", "public_share" },
                spoiler_levels = new[] { "none", "mild", "known_table_facts", "gm_secret" },
                render_requires_prompt_approval = true
            });
        });

    [HttpPost("/gm/campaigns/{campaignId}/video-foundry/new")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<PromptDraftProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> CreatePrompt(
        [FromRoute] string campaignId,
        [FromBody] CreatePromptDraftRequest? request,
        CancellationToken cancellationToken)
        => request is null
            ? BadRequest("prompt draft payload is required.")
            : await WithUser(cancellationToken, userId => Ok(_foundry.CreatePromptDraft(userId, campaignId, null, request)));

    [HttpGet("/gm/campaigns/{campaignId}/video-foundry/prompts/{promptDraftId}")]
    [ProducesResponseType<GmSessionVideoFoundryHomeProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> Prompt(
        [FromRoute] string campaignId,
        [FromRoute] string promptDraftId,
        CancellationToken cancellationToken)
        => await WithUser(cancellationToken, userId =>
        {
            GmSessionVideoFoundryHomeProjection home = _foundry.GetHome(userId, campaignId);
            return home.PromptDrafts.Any(item => string.Equals(item.Id, promptDraftId, StringComparison.OrdinalIgnoreCase))
                ? Ok(home)
                : NotFound($"Unknown prompt draft: {promptDraftId}");
        });

    [HttpPost("/gm/campaigns/{campaignId}/video-foundry/prompts/{promptDraftId}")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<PromptDraftProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> EditPrompt(
        [FromRoute] string campaignId,
        [FromRoute] string promptDraftId,
        [FromBody] EditPromptDraftRequest? request,
        CancellationToken cancellationToken)
        => request is null
            ? BadRequest("prompt edit payload is required.")
            : await WithUser(cancellationToken, userId => Ok(_foundry.EditPromptDraft(userId, campaignId, promptDraftId, request)));

    [HttpPost("/gm/campaigns/{campaignId}/video-foundry/prompts/{promptDraftId}/regenerate")]
    [ProducesResponseType<PromptDraftProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> RegeneratePrompt(
        [FromRoute] string campaignId,
        [FromRoute] string promptDraftId,
        CancellationToken cancellationToken)
        => await WithUser(cancellationToken, userId => Ok(_foundry.RegeneratePromptOnly(userId, campaignId, promptDraftId)));

    [HttpPost("/gm/campaigns/{campaignId}/video-foundry/prompts/{promptDraftId}/approve")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<SessionVideoRenderJobProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> ApprovePrompt(
        [FromRoute] string campaignId,
        [FromRoute] string promptDraftId,
        [FromBody] ApprovePromptDraftRequest? request,
        CancellationToken cancellationToken)
        => request is null
            ? BadRequest("prompt approval payload is required.")
            : await WithUser(cancellationToken, userId => Ok(_foundry.ApprovePrompt(userId, campaignId, promptDraftId, request)));

    [HttpGet("/gm/campaigns/{campaignId}/video-foundry/jobs/{jobId}")]
    [ProducesResponseType<GmSessionVideoFoundryHomeProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> Job(
        [FromRoute] string campaignId,
        [FromRoute] string jobId,
        CancellationToken cancellationToken)
        => await WithUser(cancellationToken, userId =>
        {
            GmSessionVideoFoundryHomeProjection home = _foundry.GetHome(userId, campaignId);
            return home.RenderJobs.Any(item => string.Equals(item.Id, jobId, StringComparison.OrdinalIgnoreCase))
                ? Ok(home)
                : NotFound($"Unknown render job: {jobId}");
        });

    [HttpPost("/gm/campaigns/{campaignId}/video-foundry/jobs/{jobId}/render")]
    [ProducesResponseType<SessionVideoRenderJobProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> StartRender(
        [FromRoute] string campaignId,
        [FromRoute] string jobId,
        CancellationToken cancellationToken)
        => await WithUser(cancellationToken, userId => Ok(_foundry.StartApprovedRender(userId, campaignId, jobId)));

    [HttpGet("/gm/campaigns/{campaignId}/sessions/{sessionId}/videos")]
    [ProducesResponseType<IReadOnlyList<SessionVideoRenderJobProjection>>(StatusCodes.Status200OK)]
    public async Task<IActionResult> SessionVideos(
        [FromRoute] string campaignId,
        [FromRoute] string sessionId,
        CancellationToken cancellationToken)
        => await WithUser(cancellationToken, userId => Ok(_foundry.ListSessionVideos(userId, campaignId, sessionId)));

    [HttpPost("/gm/campaigns/{campaignId}/sessions/{sessionId}/videos")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<PromptDraftProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> CreateSessionPrompt(
        [FromRoute] string campaignId,
        [FromRoute] string sessionId,
        [FromBody] CreatePromptDraftRequest? request,
        CancellationToken cancellationToken)
        => request is null
            ? BadRequest("session video payload is required.")
            : await WithUser(cancellationToken, userId => Ok(_foundry.CreatePromptDraft(userId, campaignId, sessionId, request)));

    [HttpGet("/gm/campaigns/{campaignId}/sessions/{sessionId}/table-pulse/videos")]
    [ProducesResponseType<IReadOnlyList<SessionVideoRenderJobProjection>>(StatusCodes.Status200OK)]
    public async Task<IActionResult> TablePulseVideos(
        [FromRoute] string campaignId,
        [FromRoute] string sessionId,
        CancellationToken cancellationToken)
        => await WithUser(cancellationToken, userId => Ok(_foundry.ListSessionVideos(userId, campaignId, sessionId)
            .Where(job => job.VideoType is "security_breach_report" or "matrix_alert" or "astral_disturbance_report" or "newsreel" or "faction_dispatch")
            .ToArray()));

    [HttpPost("/gm/campaigns/{campaignId}/sessions/{sessionId}/table-pulse/videos")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<TablePulseMediaPacketProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> CreateTablePulsePacket(
        [FromRoute] string campaignId,
        [FromRoute] string sessionId,
        [FromBody] CreatePromptDraftRequest? request,
        CancellationToken cancellationToken)
        => request is null
            ? BadRequest("table pulse video payload is required.")
            : await WithUser(cancellationToken, userId => Ok(_foundry.BuildTablePulseMediaPacket(
                userId,
                campaignId,
                sessionId,
                request,
                "heat threshold crossed",
                "faction reaction pending GM approval",
                "private campaign location alias")));

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
