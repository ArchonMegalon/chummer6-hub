using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
public sealed class OriginDossierFirstPartyDocumentsController : ControllerBase
{
    private readonly HubIdentityClient _identity;
    private readonly AccountService _accounts;
    private readonly OriginDossierFirstPartyDocumentService _documents;

    public OriginDossierFirstPartyDocumentsController(
        HubIdentityClient identity,
        AccountService accounts,
        OriginDossierFirstPartyDocumentService documents)
    {
        _identity = identity;
        _accounts = accounts;
        _documents = documents;
    }

    [HttpPost("/account/work/origin-dossiers/{projectId}/first-party/preview")]
    [RequestSizeLimit(OriginDossierFirstPartyDocumentService.MaxRequestBodyBytes)]
    [ProducesResponseType<OriginDossierFirstPartyDocumentProjection>(StatusCodes.Status200OK)]
    public async Task<IActionResult> Preview(
        [FromRoute] string projectId,
        [FromBody] OriginDossierFirstPartyDocumentRequest? request,
        CancellationToken cancellationToken)
    {
        ApplyPrivateNoStoreHeaders();
        return request is null
            ? BadRequest("Origin Dossier first-party preview payload is required.")
            : await WithOwner(
                cancellationToken,
                (userId, subjectId) => Ok(_documents.Preview(userId, subjectId, projectId, request)),
                requireFreshSubject: true);
    }

    [HttpGet("/account/work/origin-dossiers/{projectId}/first-party/{revisionId}")]
    [ProducesResponseType<OriginDossierFirstPartyDocumentProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Get(
        [FromRoute] string projectId,
        [FromRoute] string revisionId,
        CancellationToken cancellationToken)
        => await WithOwner(
            cancellationToken,
            (userId, subjectId) => _documents.GetForOwner(userId, subjectId, projectId, revisionId) is { } projection
                ? Ok(projection)
                : NotFound("Origin Dossier first-party preview was not found for this owner."));

    [HttpPost("/account/work/origin-dossiers/{projectId}/first-party/{revisionId}/export")]
    [ProducesResponseType<OriginDossierFirstPartyDocumentProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Export(
        [FromRoute] string projectId,
        [FromRoute] string revisionId,
        CancellationToken cancellationToken)
        => await WithOwner(
            cancellationToken,
            (userId, subjectId) => Ok(_documents.Export(userId, subjectId, projectId, revisionId)),
            requireFreshSubject: true);

    [HttpDelete("/account/work/origin-dossiers/{projectId}/first-party/{revisionId}")]
    [ProducesResponseType(StatusCodes.Status204NoContent)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Delete(
        [FromRoute] string projectId,
        [FromRoute] string revisionId,
        CancellationToken cancellationToken)
        => await WithOwner(
            cancellationToken,
            (userId, subjectId) => _documents.DeleteForOwner(userId, subjectId, projectId, revisionId)
                ? NoContent()
                : NotFound("Origin Dossier first-party preview was not found for this owner."),
            requireFreshSubject: true);

    [HttpGet("/account/work/origin-dossiers/{projectId}/first-party/{revisionId}/export.{format}")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Download(
        [FromRoute] string projectId,
        [FromRoute] string revisionId,
        [FromRoute] string format,
        CancellationToken cancellationToken)
        => await WithOwner(
            cancellationToken,
            (userId, subjectId) =>
            {
                OriginDossierFirstPartyExportArtifact artifact = _documents.GetExportArtifactForOwner(
                    userId,
                    subjectId,
                    projectId,
                    revisionId,
                    format);
                Response.Headers.ETag = $"\"sha256:{artifact.Sha256}\"";
                return File(
                    System.Text.Encoding.UTF8.GetBytes(artifact.Content),
                    artifact.ContentType,
                    artifact.FileName);
            });

    private async Task<IActionResult> WithOwner(
        CancellationToken cancellationToken,
        Func<string, string, IActionResult> action,
        bool requireFreshSubject = false)
    {
        ApplyPrivateNoStoreHeaders();
        try
        {
            var subject = requireFreshSubject
                ? await _identity.RequireFreshSubjectAsync(Request, cancellationToken)
                : await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return action(user.UserId, subject.SubjectId);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(ex.Message);
        }
        catch (InvalidDataException ex)
        {
            return Conflict(new ProblemDetails { Status = StatusCodes.Status409Conflict, Detail = ex.Message });
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

    private void ApplyPrivateNoStoreHeaders()
        => global::Chummer.Run.Api.PrivateResponseCacheHeaders.Apply(Response.Headers);
}
