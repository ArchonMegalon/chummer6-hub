using System.Diagnostics;
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
    HorizonArtifactRequestService admission, OriginSceneMediaClient media,
    ILogger<AndroidLinkedOriginScenesController>? logger = null) : ControllerBase
{
    [HttpPost("request")]
    [RequestSizeLimit(16384)]
    public Task<ActionResult> RequestScene([FromBody] AndroidOriginSceneRequest request, CancellationToken ct)
        => WithOwner("request", request.InstallationId, async (subject, current, phase) =>
        {
            if (request.AutomaticInsertion && (request.SceneExcerpt != "" || request.AltText != ""))
                throw new ArgumentException("Automatic book scenes are composed from the accepted chapter.");
            phase("compose");
            var composed = (request.AutomaticInsertion
                ? bridge.ComposeAutomatic(subject, request.ChapterRequestId, request.TextDigest, request.ExternalProcessingConsent, current)
                : bridge.Compose(subject, request.ChapterRequestId, request.TextDigest, request.SceneExcerpt,
                    request.AltText, request.ExternalProcessingConsent, current));
            phase("account");
            var user = accounts.GetBySubject(subject) ?? throw new UnauthorizedAccessException();
            composed = composed with { UserId = user.UserId, Email = user.Email };
            phase("media-health");
            await media.EnsureDispatchAvailableAsync(ct);
            if (!current()) throw new UnauthorizedAccessException();
            ct.ThrowIfCancellationRequested();
            phase("admission");
            var receipt = admission.AdmitPrivateOriginScene(composed);
            // Admission atomically commits the exact order and its allowance.
            // A phone disconnect after that boundary must not strand it before
            // Media receives it. Await one bounded handoff (the client's existing
            // deadline still applies), never fire-and-forget or replay a provider
            // request. Install revocation is still checked before and after I/O.
            phase("media-render");
            return Ok(await media.RenderAsync(subject, receipt, current, CancellationToken.None));
        });

    [HttpPost("read")]
    [RequestSizeLimit(4096)]
    public Task<ActionResult> ReadScene([FromBody] AndroidOriginSceneRead request, CancellationToken ct)
        => WithOwner("read", request.InstallationId, async (subject, current, phase) =>
        {
            phase("chapter-identity");
            string identity = bridge.ResolveIdentity(subject, request.ChapterRequestId, request.TextDigest, current);
            phase("media-read");
            try { return Ok(await media.ReadAsync(subject, identity, current, ct)); }
            catch (KeyNotFoundException)
            {
                // A missing Media row does not prove that no order was charged:
                // Hub may have stopped after admission but before the handoff.
                // Consult the durable ledger read-only; never dispatch from read.
                phase("admission-read");
                var user = accounts.GetBySubject(subject) ?? throw new UnauthorizedAccessException();
                if (admission.FindPrivateOriginScene(user.UserId, subject, identity) is null) throw;
                ct.ThrowIfCancellationRequested();
                // This existing wire state deliberately claims neither a running
                // render nor completion. Older phones must not interpret it as
                // NotFound and offer another consented creation automatically.
                return Ok(new { AssetId = identity, State = "uncertain", PublicationAuthorized = false });
            }
        });

    [HttpPost("decide")]
    [RequestSizeLimit(4096)]
    public Task<ActionResult> DecideScene([FromBody] AndroidOriginSceneDecision request, CancellationToken ct)
        => WithOwner("decide", request.InstallationId, async (subject, current, phase) =>
        {
            phase("chapter-identity");
            string identity = bridge.ResolveIdentity(subject, request.ChapterRequestId, request.TextDigest, current);
            phase("media-decision");
            return Ok(await media.DecideAsync(subject, identity, request.ExpectedImageHash,
                request.Approve, request.ExplicitlyConfirmed, current, ct));
        });

    private string? CurrentSubject(string installationId)
        => AndroidLinkedV2RequestProof.TryGetPrincipal(HttpContext, out var principal)
            && principal!.Installation.InstallationId == installationId
            ? linking.ResolveAndroidLinkedV2Principal(principal, requireAvailableAuthority: true)?.SubjectId : null;

    private async Task<ActionResult> WithOwner(string operation, string installationId,
        Func<string, Func<bool>, Action<string>, Task<ActionResult>> action)
    {
        AndroidLinkedV2RequestProofMiddleware.ApplyPrivateResponseHeaders(Response.Headers);
        long started = Stopwatch.GetTimestamp();
        string phase = "authorization";
        int authorityChecks = 0;
        long authorityMilliseconds = 0;
        string? ObserveSubject()
        {
            long checking = Stopwatch.GetTimestamp();
            authorityChecks++;
            try { return CurrentSubject(installationId); }
            finally { authorityMilliseconds += (long)Stopwatch.GetElapsedTime(checking).TotalMilliseconds; }
        }
        void Diagnose(string failure)
        {
            // Only code-owned labels and elapsed time: never exception objects,
            // identifiers, request bodies, manuscripts, URLs or credentials.
            logger?.LogWarning("Private Origin scene {Operation} failed at {Phase} ({Failure}, {ElapsedMilliseconds} ms; authority {AuthorityChecks}/{AuthorityMilliseconds} ms; caller canceled {CallerCanceled}).",
                operation, phase, failure, (long)Stopwatch.GetElapsedTime(started).TotalMilliseconds,
                authorityChecks, authorityMilliseconds, HttpContext.RequestAborted.IsCancellationRequested);
        }
        try
        {
            if (!AndroidLinkedV2RequestProof.TryGetPrincipal(HttpContext, out var principal)
                || principal!.Installation.InstallationId != installationId
                || principal.Installation.SubjectId is not { Length: > 0 } subject) return Unauthorized();
            bool Current() => ObserveSubject() == subject;
            if (!media.IsConfigured)
                return Current() ? StatusCode(503, "Chapter illustrations are not enabled on this server.") : Unauthorized();
            // All three actions enter the bridge first. It checks current
            // installation authority BEFORE reading a chapter and again before
            // returning private data. Do not repeat that same remote probe here;
            // the middleware principal supplies identity, never cached authority.
            // Account lookup follows composition, and admission/media/disclosure
            // keep their own fresh checks after intervening I/O.
            ActionResult result = await action(subject, Current, value => phase = value);
            phase = "final-authorization";
            return Current() ? result : Unauthorized();
        }
        catch (UnauthorizedAccessException) { Diagnose("unauthorized"); return Unauthorized(); }
        catch (KeyNotFoundException) { return NotFound(); }
        catch (ArgumentException) { Diagnose("invalid-input"); return BadRequest("Select a scene from the current accepted chapter."); }
        catch (InvalidOperationException) { Diagnose("conflict"); return Conflict("Reopen the existing illustration request before continuing."); }
        catch (InstallLinkingOperationException error) when (error.StatusCode == 503)
        { Diagnose("authority-unavailable"); return StatusCode(503, "Private illustration authorization is unavailable."); }
        catch (Exception error) when (error is IOException or JsonException or HttpRequestException or OperationCanceledException)
        { Diagnose(error is OperationCanceledException ? "interrupted" : error is JsonException ? "invalid-response" : "io-unavailable");
            return StatusCode(503, "Illustration service unavailable. Read the existing request; do not create a duplicate."); }
    }
}

public sealed record AndroidOriginSceneRequest(string InstallationId, string ChapterRequestId, string TextDigest,
    string SceneExcerpt, string AltText, bool ExternalProcessingConsent, bool AutomaticInsertion = false);
public sealed record AndroidOriginSceneRead(string InstallationId, string ChapterRequestId, string TextDigest);
public sealed record AndroidOriginSceneDecision(string InstallationId, string ChapterRequestId, string TextDigest,
    string ExpectedImageHash, bool Approve, bool ExplicitlyConfirmed);
