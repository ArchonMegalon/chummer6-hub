using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class InternalHorizonCapabilitiesController : ControllerBase
{
    private readonly HorizonCapabilityService _capabilities;
    private readonly HorizonArtifactQuotaService _quota;
    private readonly HorizonArtifactRequestService _artifactRequests;
    private readonly IConfiguration _configuration;

    public InternalHorizonCapabilitiesController(
        HorizonCapabilityService capabilities,
        HorizonArtifactQuotaService quota,
        HorizonArtifactRequestService artifactRequests,
        IConfiguration configuration)
    {
        _capabilities = capabilities;
        _quota = quota;
        _artifactRequests = artifactRequests;
        _configuration = configuration;
    }

    [HttpGet("/api/internal/horizons/capabilities")]
    [ProducesResponseType<HorizonCapabilityHealthCatalog>(StatusCodes.Status200OK)]
    public ActionResult<HorizonCapabilityHealthCatalog> ListCapabilities([FromQuery] bool publicSafe = false)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        HorizonCapabilityHealthSnapshot[] capabilities = _capabilities.ListCapabilities()
            .Select(item => _capabilities.GetHealth(item.HorizonId, item.CapabilityId, publicSafe))
            .ToArray();
        return Ok(new HorizonCapabilityHealthCatalog(publicSafe, capabilities));
    }

    [HttpPost("/api/internal/horizons/artifact-requests")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<HorizonArtifactRequestReceipt>(StatusCodes.Status200OK)]
    public ActionResult<HorizonArtifactRequestReceipt> BuildArtifactRequest([FromBody] HorizonArtifactRequestCreateRequest? request)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        if (request is null)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, detail: "horizon artifact request is required.");
        }

        try
        {
            return Ok(_artifactRequests.BuildRequest(request, consumeQuota: true));
        }
        catch (KeyNotFoundException ex)
        {
            return Problem(statusCode: StatusCodes.Status404NotFound, detail: ex.Message);
        }
    }

    [HttpGet("/api/internal/horizons/artifact-requests")]
    [ProducesResponseType<HorizonArtifactRequestReceiptCatalog>(StatusCodes.Status200OK)]
    public ActionResult<HorizonArtifactRequestReceiptCatalog> ListArtifactRequests(
        [FromQuery] string? horizonId = null,
        [FromQuery] string? userId = null,
        [FromQuery] string? artifactKindOrCapabilityId = null,
        [FromQuery] int limit = 50)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        IReadOnlyList<HorizonArtifactRequestReceipt> receipts = _artifactRequests.ListRecentReceipts(horizonId, userId, artifactKindOrCapabilityId, limit);
        return Ok(new HorizonArtifactRequestReceiptCatalog(
            HorizonId: string.IsNullOrWhiteSpace(horizonId) ? null : horizonId.Trim(),
            UserId: string.IsNullOrWhiteSpace(userId) ? null : userId.Trim(),
            Receipts: receipts,
            ArtifactKindOrCapabilityId: string.IsNullOrWhiteSpace(artifactKindOrCapabilityId) ? null : artifactKindOrCapabilityId.Trim()));
    }

    [HttpGet("/api/internal/horizons/quotas")]
    [ProducesResponseType<HorizonArtifactQuotaCatalog>(StatusCodes.Status200OK)]
    public ActionResult<HorizonArtifactQuotaCatalog> ListQuotas(
        [FromQuery] string userId,
        [FromQuery] string? email = null,
        [FromQuery] string? horizonId = null,
        [FromQuery] string? artifactKindOrCapabilityId = null,
        [FromQuery] bool publicVisibleOnly = false)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        try
        {
            IReadOnlyList<HorizonArtifactQuotaSnapshot> quotas = _quota.ListQuotas(
                new HorizonArtifactQuotaCatalogRequest(
                    UserId: userId,
                    HorizonId: horizonId,
                    ArtifactKindOrCapabilityId: artifactKindOrCapabilityId,
                    Email: email,
                    PublicVisibleOnly: publicVisibleOnly));
            return Ok(new HorizonArtifactQuotaCatalog(
                UserId: string.IsNullOrWhiteSpace(userId) ? string.Empty : userId.Trim(),
                HorizonId: string.IsNullOrWhiteSpace(horizonId) ? null : horizonId.Trim(),
                ArtifactKindOrCapabilityId: string.IsNullOrWhiteSpace(artifactKindOrCapabilityId) ? null : artifactKindOrCapabilityId.Trim(),
                PublicVisibleOnly: publicVisibleOnly,
                Quotas: quotas));
        }
        catch (BrilliantDirectoriesBillingUnavailableException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    private ActionResult? RequireInternalAutomationAuth()
    {
        string expectedToken = (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(expectedToken))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "internal horizon capability authorization is not configured.");
        }

        string header = Request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal horizon capability authorization is required.");
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        return FixedTimeEquals(providedToken, expectedToken)
            ? null
            : Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal horizon capability authorization is required.");
    }

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.UTF8.GetBytes(left);
        byte[] rightBytes = Encoding.UTF8.GetBytes(right);
        return leftBytes.Length == rightBytes.Length
            && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }
}

public sealed record HorizonCapabilityHealthCatalog(
    bool PublicSafe,
    IReadOnlyList<HorizonCapabilityHealthSnapshot> Capabilities);

public sealed record HorizonArtifactRequestReceiptCatalog(
    string? HorizonId,
    string? UserId,
    IReadOnlyList<HorizonArtifactRequestReceipt> Receipts,
    string? ArtifactKindOrCapabilityId = null);
