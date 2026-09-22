using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

/// <summary>Signed-install private requests. No provider execution or public download routes.</summary>
[ApiController]
[Route("api/v2/android/linked/origin/chapters")]
public sealed class AndroidLinkedOriginChaptersController(
    InstallLinkingService installLinking, OriginChapterAuthoringService authoring) : ControllerBase
{
    [HttpPost("request")]
    [RequestSizeLimit(OriginChapterAuthoringService.MaximumRequestBytes)]
    public ActionResult<OriginChapterAuthoringJob> RequestChapter([FromBody] AndroidLinkedOriginChapterRequest? request)
        => WithOwner(request?.InstallationId, subject => request?.Authoring is null
            ? BadRequest() : Ok(authoring.Create(subject, request.Authoring, () => CurrentSubject(request.InstallationId) == subject)));

    [HttpPost("read")]
    [RequestSizeLimit(4096)]
    public ActionResult<OriginChapterAuthoringJob> ReadChapter([FromBody] AndroidLinkedOriginChapterReadRequest? request)
        => WithOwner(request?.InstallationId, subject => authoring.Get(subject, request!.RequestId) is { } job
            ? Ok(job) : NotFound());

    [HttpPost("accept")]
    [RequestSizeLimit(4096)]
    public ActionResult<OriginChapterAuthoringJob> AcceptChapter([FromBody] AndroidLinkedOriginChapterAcceptRequest? request)
        => WithOwner(request?.InstallationId, subject => Ok(authoring.AcceptReading(subject, request!.RequestId,
            request.SourceDigest, request.ProviderReceiptDigest, request.TextDigest, request.ExplicitlyConfirmed,
            () => CurrentSubject(request.InstallationId) == subject)));

    private string? CurrentSubject(string? installationId)
        => installationId is not null
            && AndroidLinkedV2RequestProof.TryGetPrincipal(HttpContext, out var principal)
            && principal!.Installation.InstallationId == installationId
            ? installLinking.ResolveAndroidLinkedV2Principal(principal)?.SubjectId : null;

    private ActionResult WithOwner(string? installationId, Func<string, ActionResult> action)
    {
        AndroidLinkedV2RequestProofMiddleware.ApplyPrivateResponseHeaders(Response.Headers);
        if (CurrentSubject(installationId) is not { Length: > 0 } subject) return Unauthorized();
        if (!authoring.IsConfigured) return StatusCode(StatusCodes.Status503ServiceUnavailable);
        try { return action(subject); }
        catch (UnauthorizedAccessException) { return Unauthorized(); }
        catch (KeyNotFoundException) { return NotFound(); }
        catch (ArgumentException) { return BadRequest("The narrative request is invalid."); }
        catch (InvalidOperationException) { return Conflict("Reopen the existing authoring request before continuing."); }
        catch (Exception error) when (error is IOException or InvalidDataException or JsonException)
        { return StatusCode(StatusCodes.Status503ServiceUnavailable, "Private authoring storage is unavailable. Check the same request before retrying."); }
    }
}

public sealed record AndroidLinkedOriginChapterRequest(string InstallationId, OriginChapterAuthoringRequest Authoring);
public sealed record AndroidLinkedOriginChapterReadRequest(string InstallationId, string RequestId);
public sealed record AndroidLinkedOriginChapterAcceptRequest(string InstallationId, string RequestId,
    string SourceDigest, string ProviderReceiptDigest, string TextDigest, bool ExplicitlyConfirmed);
