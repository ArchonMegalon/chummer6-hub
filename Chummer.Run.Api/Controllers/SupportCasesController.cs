using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.Support;
using Microsoft.AspNetCore.Mvc;
using System.Security.Cryptography;
using System.Text;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
[Route("api/v1/support/cases")]
public sealed class SupportCasesController : ControllerBase
{
    private readonly HubIdentityClient _identity;
    private readonly AccountService _accounts;
    private readonly SupportCaseService _supportCases;
    private readonly SupportAssistantService _assistant;
    private readonly IConfiguration _configuration;

    public SupportCasesController(
        HubIdentityClient identity,
        AccountService accounts,
        SupportCaseService supportCases,
        SupportAssistantService assistant,
        IConfiguration configuration)
    {
        _identity = identity;
        _accounts = accounts;
        _supportCases = supportCases;
        _assistant = assistant;
        _configuration = configuration;
    }

    [HttpGet("me")]
    [ProducesResponseType<SupportCaseListResponse>(StatusCodes.Status200OK)]
    public async Task<ActionResult<SupportCaseListResponse>> GetMyCases(
        [FromQuery] string? status,
        [FromQuery] string? kind,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_supportCases.ListForReporter(user.UserId, subject.SubjectId, status, kind));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("{caseId}")]
    [ProducesResponseType<SupportCaseProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<SupportCaseProjection>> GetCase([FromRoute] string caseId, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(caseId))
        {
            return BadRequest("caseId is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            SupportCaseProjection? item = _supportCases.GetForReporter(caseId, user.UserId, subject.SubjectId);
            return item is null ? NotFound() : Ok(item);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost]
    [ProducesResponseType<SupportCaseProjection>(StatusCodes.Status202Accepted)]
    public async Task<ActionResult<SupportCaseProjection>> Submit(
        [FromBody] SupportCaseSubmitRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("support case payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            SupportCaseProjection created = _supportCases.Submit(user.UserId, subject.SubjectId, request);
            return AcceptedAtAction(nameof(GetCase), new { caseId = created.CaseId }, created);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("assistant")]
    [ProducesResponseType<SupportAssistantResponse>(StatusCodes.Status200OK)]
    public async Task<ActionResult<SupportAssistantResponse>> AskAssistant(
        [FromBody] SupportAssistantRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("assistant payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_assistant.Answer(user.UserId, subject.SubjectId, request));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpGet("triage")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<SupportCaseListResponse>(StatusCodes.Status200OK)]
    public ActionResult<SupportCaseListResponse> ListForTriage(
        [FromQuery] string? status = null,
        [FromQuery] string? kind = null,
        [FromQuery] string? candidateOwnerRepo = null,
        [FromQuery] bool? designImpactOnly = null)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        return Ok(_supportCases.ListForAutomation(status, kind, candidateOwnerRepo, designImpactOnly));
    }

    [HttpPost("{caseId}/transition")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<SupportCaseProjection>(StatusCodes.Status200OK)]
    public ActionResult<SupportCaseProjection> Transition([FromRoute] string caseId, [FromBody] SupportCaseTransitionRequest? request)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        if (request is null)
        {
            return BadRequest("transition payload is required.");
        }

        try
        {
            return Ok(_supportCases.Transition(caseId, request));
        }
        catch (Exception ex) when (ex is KeyNotFoundException or ArgumentException or InvalidOperationException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    [HttpPost("{caseId}/notify")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<SupportCaseProjection>(StatusCodes.Status200OK)]
    public ActionResult<SupportCaseProjection> NotifyReporter([FromRoute] string caseId, [FromBody] SupportCaseNotificationRequest? request)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        if (request is null)
        {
            return BadRequest("notification payload is required.");
        }

        try
        {
            return Ok(_supportCases.RecordNotification(caseId, request));
        }
        catch (Exception ex) when (ex is KeyNotFoundException or ArgumentException or InvalidOperationException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }

    private ActionResult? RequireInternalAutomationAuth()
    {
        string expectedToken = (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(expectedToken))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "internal support automation auth is not configured.");
        }

        string header = Request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal support automation authorization is required.");
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        if (!FixedTimeEquals(providedToken, expectedToken))
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal support automation authorization is required.");
        }

        return null;
    }

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.UTF8.GetBytes(left);
        byte[] rightBytes = Encoding.UTF8.GetBytes(right);
        return CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }
}
