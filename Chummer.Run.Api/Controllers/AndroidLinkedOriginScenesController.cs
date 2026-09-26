using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

/// <summary>Owner-bound private media bridge. No provider URL/credential reaches Android.</summary>
[ApiController]
[Route("api/v2/android/linked/origin/scenes")]
public sealed class AndroidLinkedOriginScenesController(InstallLinkingService linking,
    AccountService accounts, OriginChapterSceneRequestBridge bridge,
    HorizonArtifactRequestService admission, OriginSceneMediaClient media) : ControllerBase
{
    [HttpPost("request")]
    [RequestSizeLimit(16384)]
    public Task<ActionResult> RequestScene([FromBody] AndroidOriginSceneRequest request, CancellationToken ct)
        => WithOwner(request.InstallationId, async (subject, current) =>
        {
            var user = accounts.GetBySubject(subject) ?? throw new UnauthorizedAccessException();
            var composed = bridge.Compose(subject, request.ChapterRequestId, request.TextDigest, request.SceneExcerpt,
                request.AltText, request.ExternalProcessingConsent, current) with { UserId = user.UserId, Email = user.Email };
            await media.EnsureDispatchAvailableAsync(ct);
            if (!current()) throw new UnauthorizedAccessException();
            var receipt = admission.AdmitPrivateOriginScene(composed);
            return Ok(await media.RenderAsync(subject, receipt, current, ct));
        });

    [HttpPost("read")]
    [RequestSizeLimit(4096)]
    public Task<ActionResult> ReadScene([FromBody] AndroidOriginSceneRead request, CancellationToken ct)
        => WithOwner(request.InstallationId, async (subject, current) =>
        {
            string identity = bridge.ResolveIdentity(subject, request.ChapterRequestId, request.TextDigest, current);
            return Ok(await media.ReadAsync(subject, identity, current, ct));
        });

    [HttpPost("decide")]
    [RequestSizeLimit(4096)]
    public Task<ActionResult> DecideScene([FromBody] AndroidOriginSceneDecision request, CancellationToken ct)
        => WithOwner(request.InstallationId, async (subject, current) =>
        {
            string identity = bridge.ResolveIdentity(subject, request.ChapterRequestId, request.TextDigest, current);
            return Ok(await media.DecideAsync(subject, identity, request.ExpectedImageHash,
                request.Approve, request.ExplicitlyConfirmed, current, ct));
        });

    private string? CurrentSubject(string installationId)
        => AndroidLinkedV2RequestProof.TryGetPrincipal(HttpContext, out var principal)
            && principal!.Installation.InstallationId == installationId
            ? linking.ResolveAndroidLinkedV2Principal(principal, requireAvailableAuthority: true)?.SubjectId : null;

    private async Task<ActionResult> WithOwner(string installationId, Func<string, Func<bool>, Task<ActionResult>> action)
    {
        AndroidLinkedV2RequestProofMiddleware.ApplyPrivateResponseHeaders(Response.Headers);
        try
        {
            if (CurrentSubject(installationId) is not { Length: > 0 } subject) return Unauthorized();
            if (!media.IsConfigured) return StatusCode(503, "Chapter illustrations are not enabled on this server.");
            bool Current() => CurrentSubject(installationId) == subject;
            ActionResult result = await action(subject, Current);
            return Current() ? result : Unauthorized();
        }
        catch (UnauthorizedAccessException) { return Unauthorized(); }
        catch (KeyNotFoundException) { return NotFound(); }
        catch (ArgumentException) { return BadRequest("Select a scene from the current accepted chapter."); }
        catch (InvalidOperationException) { return Conflict("Reopen the existing illustration request before continuing."); }
        catch (InstallLinkingOperationException error) when (error.StatusCode == 503)
        { return StatusCode(503, "Private illustration authorization is unavailable."); }
        catch (Exception error) when (error is IOException or JsonException or HttpRequestException or OperationCanceledException)
        { return StatusCode(503, "Illustration service unavailable. Read the existing request; do not create a duplicate."); }
    }
}

public sealed record AndroidOriginSceneRequest(string InstallationId, string ChapterRequestId, string TextDigest,
    string SceneExcerpt, string AltText, bool ExternalProcessingConsent);
public sealed record AndroidOriginSceneRead(string InstallationId, string ChapterRequestId, string TextDigest);
public sealed record AndroidOriginSceneDecision(string InstallationId, string ChapterRequestId, string TextDigest,
    string ExpectedImageHash, bool Approve, bool ExplicitlyConfirmed);
