using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class HorizonArtifactRequestsController : ControllerBase
{
    private readonly HorizonArtifactRequestService _requests;
    private readonly AccountService? _accounts;
    private readonly HubIdentityClient? _identity;
    private readonly ILogger<HorizonArtifactRequestsController> _logger;

    public HorizonArtifactRequestsController(
        HorizonArtifactRequestService requests,
        AccountService? accounts = null,
        HubIdentityClient? identity = null,
        ILogger<HorizonArtifactRequestsController>? logger = null)
    {
        _requests = requests;
        _accounts = accounts;
        _identity = identity;
        _logger = logger ?? NullLogger<HorizonArtifactRequestsController>.Instance;
    }

    [HttpGet("/api/v1/horizons/artifact-requests/me")]
    [ProducesResponseType<HorizonArtifactRequestReceiptCatalog>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public async Task<ActionResult<HorizonArtifactRequestReceiptCatalog>> MyArtifactRequests(
        [FromQuery] string? horizonId = null,
        [FromQuery] string? artifactKindOrCapabilityId = null,
        [FromQuery] int limit = 50,
        CancellationToken cancellationToken = default)
    {
        ResolvedHorizonActor? actor = await TryGetCurrentActorAsync(cancellationToken).ConfigureAwait(false);
        if (actor is null)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "Sign in before checking horizon artifact requests.");
        }

        IReadOnlyList<HorizonArtifactRequestReceipt> receipts = _requests.ListRecentReceipts(
            horizonId,
            actor.UserId,
            artifactKindOrCapabilityId,
            limit);
        return Ok(new HorizonArtifactRequestReceiptCatalog(
            HorizonId: TrimToNull(horizonId),
            UserId: actor.UserId,
            Receipts: receipts,
            ArtifactKindOrCapabilityId: TrimToNull(artifactKindOrCapabilityId)));
    }

    [HttpGet("/api/v1/horizons/artifact-requests/me/{requestId}")]
    [ProducesResponseType<HorizonArtifactRequestReceipt>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<HorizonArtifactRequestReceipt>> MyArtifactRequest(
        [FromRoute] string requestId,
        CancellationToken cancellationToken = default)
    {
        ResolvedHorizonActor? actor = await TryGetCurrentActorAsync(cancellationToken).ConfigureAwait(false);
        if (actor is null)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "Sign in before checking a horizon artifact request.");
        }

        HorizonArtifactRequestReceipt? receipt = _requests.FindReceiptForUser(requestId, actor.UserId);
        return receipt is null
            ? NotFound()
            : Ok(receipt);
    }

    [HttpGet("/api/v1/public/horizons/artifact-requests/{requestId}")]
    [ProducesResponseType<PublicHorizonArtifactRequestReceipt>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<PublicHorizonArtifactRequestReceipt> PublicArtifactRequest([FromRoute] string requestId)
    {
        HorizonArtifactRequestReceipt? receipt = _requests.FindAcceptedPublicSafeReceipt(requestId);
        return receipt is null
            ? NotFound()
            : Ok(BuildPublicReceipt(receipt));
    }

    private async Task<ResolvedHorizonActor?> TryGetCurrentActorAsync(CancellationToken cancellationToken)
    {
        if (_identity is null)
        {
            return null;
        }

        try
        {
            AuthenticatedHubSubject subject = await _identity.RequireSubjectAsync(Request, cancellationToken).ConfigureAwait(false);
            string userId = _accounts?.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email).UserId
                ?? subject.SubjectId;
            return new ResolvedHorizonActor(userId);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return null;
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Horizon artifact request surface could not resolve the current signed-in subject.");
            return null;
        }
    }

    private static string? TrimToNull(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private sealed record ResolvedHorizonActor(string UserId);

    private static PublicHorizonArtifactRequestReceipt BuildPublicReceipt(HorizonArtifactRequestReceipt receipt)
    {
        string encodedHorizonId = Uri.EscapeDataString(receipt.HorizonId);
        string encodedCapabilityId = Uri.EscapeDataString(receipt.CapabilityId);
        string encodedRequestId = Uri.EscapeDataString(receipt.RequestId);
        return new PublicHorizonArtifactRequestReceipt(
            RequestId: receipt.RequestId,
            Status: receipt.Status,
            HorizonId: receipt.HorizonId,
            CapabilityId: receipt.CapabilityId,
            ArtifactKind: receipt.ArtifactKind,
            PublicLabel: receipt.PublicLabel,
            CapabilitySlot: receipt.CapabilitySlot,
            SourceRef: receipt.SourceRef,
            Visibility: receipt.Visibility,
            PublicSafe: true,
            CreatedAtUtc: receipt.CreatedAtUtc,
            QuotaTracked: receipt.QuotaTracked,
            CapabilityHealthHref: $"/api/v1/public/horizons/capabilities?horizonId={encodedHorizonId}&artifactKindOrCapabilityId={encodedCapabilityId}",
            PublicReceiptHref: $"/api/v1/public/horizons/artifact-requests/{encodedRequestId}");
    }
}

public sealed record PublicHorizonArtifactRequestReceipt(
    string RequestId,
    string Status,
    string HorizonId,
    string CapabilityId,
    string ArtifactKind,
    string PublicLabel,
    string CapabilitySlot,
    string SourceRef,
    string Visibility,
    bool PublicSafe,
    DateTimeOffset CreatedAtUtc,
    bool QuotaTracked,
    string CapabilityHealthHref,
    string PublicReceiptHref);
