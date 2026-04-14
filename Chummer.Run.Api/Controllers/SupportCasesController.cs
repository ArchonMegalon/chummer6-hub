using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Chummer.Control.Contracts.Support;
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
    private readonly IdentityLinkService _links;
    private readonly SupportCaseService _supportCases;
    private readonly SupportCasePresentationService _supportPresentation;
    private readonly SupportAssistantService _assistant;
    private readonly SupportAttachmentStorageService _attachments;
    private readonly IConfiguration _configuration;
    private readonly InstallLinkingService _installLinking;

    public SupportCasesController(
        HubIdentityClient identity,
        AccountService accounts,
        IdentityLinkService links,
        SupportCaseService supportCases,
        SupportCasePresentationService supportPresentation,
        SupportAssistantService assistant,
        SupportAttachmentStorageService attachments,
        InstallLinkingService installLinking,
        IConfiguration configuration)
    {
        _identity = identity;
        _accounts = accounts;
        _links = links;
        _supportCases = supportCases;
        _supportPresentation = supportPresentation;
        _assistant = assistant;
        _attachments = attachments;
        _installLinking = installLinking;
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

    [HttpGet("me/presented")]
    [ProducesResponseType<IReadOnlyList<SupportCaseDigestViewModel>>(StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<SupportCaseDigestViewModel>>> GetMyPresentedCases(
        [FromQuery] string? status,
        [FromQuery] string? kind,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var items = _supportCases.ListForReporter(user.UserId, subject.SubjectId, status, kind).Items;
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(_supportPresentation.BuildDigestList(items, installLinking));
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

    [HttpGet("{caseId}/attachments/{attachmentId}")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> DownloadAttachment(
        [FromRoute] string caseId,
        [FromRoute] string attachmentId,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(caseId) || string.IsNullOrWhiteSpace(attachmentId))
        {
            return NotFound();
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            SupportCaseProjection? item = _supportCases.GetForReporter(caseId, user.UserId, subject.SubjectId);
            if (item?.Attachments?.Any(candidate => string.Equals(candidate.AttachmentId, attachmentId, StringComparison.OrdinalIgnoreCase)) != true)
            {
                return NotFound();
            }

            var stored = _attachments.TryOpenAttachment(caseId, attachmentId);
            return stored is null
                ? NotFound()
                : File(stored.Value.Stream, stored.Value.ContentType, stored.Value.FileName);
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
            string? reporterEmail = ResolveReporterEmail(user.UserId, subject.Email, request.ReporterEmail);
            SupportCaseProjection created = _supportCases.Submit(
                user.UserId,
                subject.SubjectId,
                request with
                {
                    ReporterEmail = reporterEmail
                });
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

    [HttpPost("form")]
    [Consumes("multipart/form-data")]
    [ProducesResponseType<SupportCaseProjection>(StatusCodes.Status202Accepted)]
    public async Task<ActionResult<SupportCaseProjection>> SubmitFromForm(
        [FromForm] string? kind,
        [FromForm] string? title,
        [FromForm] string? summary,
        [FromForm] string? detail,
        [FromForm] string? installationId,
        [FromForm] string? applicationVersion,
        [FromForm] string? releaseChannel,
        [FromForm] string? headId,
        [FromForm] string? platform,
        [FromForm] string? arch,
        [FromForm] List<IFormFile>? attachments,
        CancellationToken cancellationToken)
    {
        var request = new SupportCaseSubmitRequest(
            Kind: kind ?? string.Empty,
            Title: title ?? string.Empty,
            Summary: summary ?? string.Empty,
            Detail: detail ?? string.Empty,
            InstallationId: installationId,
            ApplicationVersion: applicationVersion,
            ReleaseChannel: releaseChannel,
            HeadId: headId,
            Platform: platform,
            Arch: arch,
            Source: SupportCaseSourceKinds.HubAccount);

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            string? reporterEmail = ResolveReporterEmail(user.UserId, subject.Email, request.ReporterEmail);
            SupportCaseProjection created = _supportCases.Submit(
                user.UserId,
                subject.SubjectId,
                request with
                {
                    ReporterEmail = reporterEmail
                },
                await ReadUploadsAsync(attachments, cancellationToken));
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

    [HttpPost("{caseId}/verify")]
    [ProducesResponseType<SupportCaseProjection>(StatusCodes.Status200OK)]
    public async Task<ActionResult<SupportCaseProjection>> VerifyReporterFix(
        [FromRoute] string caseId,
        [FromBody] SupportCaseVerificationRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("verification payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            SupportCaseProjection? trackedCase = _supportCases.GetForReporter(caseId, user.UserId, subject.SubjectId);
            if (trackedCase is null)
            {
                return NotFound();
            }

            if (AllowsReporterVerification(trackedCase.Status))
            {
                var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
                var presented = _supportPresentation.Build(trackedCase, installLinking);
                if (!presented.CanVerifyFix)
                {
                    string detail = !string.IsNullOrWhiteSpace(presented.VerificationSummary)
                        ? presented.VerificationSummary
                        : !string.IsNullOrWhiteSpace(presented.InstallReadinessSummary)
                            ? presented.InstallReadinessSummary
                            : presented.NextSafeAction;
                    return Problem(statusCode: StatusCodes.Status409Conflict, detail: detail);
                }
            }

            return Ok(_supportCases.VerifyForReporter(caseId, user.UserId, subject.SubjectId, request));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or ArgumentException or InvalidOperationException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
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

    private static bool AllowsReporterVerification(string? status)
        => string.Equals(status, SupportCaseStatuses.Fixed, StringComparison.OrdinalIgnoreCase)
           || string.Equals(status, SupportCaseStatuses.ReleasedToReporterChannel, StringComparison.OrdinalIgnoreCase)
           || string.Equals(status, SupportCaseStatuses.UserNotified, StringComparison.OrdinalIgnoreCase);

    private static async Task<IReadOnlyList<SupportAttachmentUpload>> ReadUploadsAsync(
        IReadOnlyList<IFormFile>? files,
        CancellationToken cancellationToken)
    {
        if (files is null || files.Count == 0)
        {
            return Array.Empty<SupportAttachmentUpload>();
        }

        List<SupportAttachmentUpload> uploads = new(files.Count);
        foreach (var file in files)
        {
            if (file.Length <= 0)
            {
                continue;
            }

            await using var stream = file.OpenReadStream();
            using var buffer = new MemoryStream();
            await stream.CopyToAsync(buffer, cancellationToken);
            uploads.Add(new SupportAttachmentUpload(file.FileName, file.ContentType, buffer.ToArray()));
        }

        return uploads;
    }

    private string? ResolveReporterEmail(string userId, string? subjectEmail, string? requestEmail)
    {
        string? explicitEmail = NormalizeOptionalEmail(requestEmail);
        if (!string.IsNullOrWhiteSpace(explicitEmail))
        {
            return explicitEmail;
        }

        string? identityEmail = NormalizeOptionalEmail(subjectEmail);
        if (!string.IsNullOrWhiteSpace(identityEmail))
        {
            return identityEmail;
        }

        LinkedIdentityDto? linkedEmail = _links.FindLinkedIdentityForUser(userId, "email");
        if (linkedEmail is not null
            && string.Equals(linkedEmail.Status, "verified", StringComparison.OrdinalIgnoreCase))
        {
            return NormalizeOptionalEmail(linkedEmail.ProviderSubject) ?? NormalizeOptionalEmail(linkedEmail.DisplayLabel);
        }

        return null;
    }

    private static string? NormalizeOptionalEmail(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string normalized = value.Trim();
        return normalized.Length <= 256 ? normalized : normalized[..256];
    }
}
