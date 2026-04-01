using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class InternalReleaseBundlesController : ControllerBase
{
    private readonly ReleaseBundlePromotionService _promotionService;
    private readonly IConfiguration _configuration;
    private readonly ReleaseUploadTicketService _releaseUploadTickets;
    private readonly PublicReleaseManifestService _releaseManifestService;
    private readonly AccountService _accounts;
    private readonly InstallLinkingService _installLinking;

    public InternalReleaseBundlesController(
        ReleaseBundlePromotionService promotionService,
        IConfiguration configuration,
        ReleaseUploadTicketService releaseUploadTickets,
        PublicReleaseManifestService releaseManifestService,
        AccountService accounts,
        InstallLinkingService installLinking)
    {
        _promotionService = promotionService;
        _configuration = configuration;
        _releaseUploadTickets = releaseUploadTickets;
        _releaseManifestService = releaseManifestService;
        _accounts = accounts;
        _installLinking = installLinking;
    }

    [HttpPost("/api/internal/releases/bundles")]
    [IgnoreAntiforgeryToken]
    [Consumes("multipart/form-data")]
    [ProducesResponseType<ReleaseBundlePromotionResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<ReleaseBundlePromotionResult>> UploadBundle(
        [FromForm] IFormFile? bundle,
        CancellationToken cancellationToken)
    {
        ReleaseBundleAuthorizationContext? authorization = RequireInternalAutomationAuth(out ActionResult? denied);
        if (denied is not null)
        {
            return denied;
        }

        if (bundle is null || bundle.Length <= 0)
        {
            return BadRequest("bundle file is required.");
        }

        try
        {
            await using Stream bundleStream = bundle.OpenReadStream();
            ReleaseBundlePromotionResult result = await _promotionService.PromoteAsync(bundle.FileName, bundleStream, cancellationToken);
            if (authorization?.UploadTicketClaims is not null)
            {
                result = AttachSignedInInstallClaims(result, authorization.UploadTicketClaims);
            }

            return Ok(result);
        }
        catch (Exception ex) when (ex is InvalidDataException or JsonException or NotSupportedException)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, detail: ex.Message);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
    }

    private ReleaseBundleAuthorizationContext? RequireInternalAutomationAuth(out ActionResult? denied)
    {
        denied = null;

        string header = Request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            denied = Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal release promotion authorization is required.");
            return null;
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        string expectedToken = (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
        if (!string.IsNullOrWhiteSpace(expectedToken) && FixedTimeEquals(providedToken, expectedToken))
        {
            return new ReleaseBundleAuthorizationContext(null);
        }

        if (_releaseUploadTickets.TryValidate(providedToken, out ReleaseUploadTicketClaims? ticketClaims))
        {
            return new ReleaseBundleAuthorizationContext(ticketClaims);
        }

        denied = Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal release promotion authorization is required.");
        return null;
    }

    private ReleaseBundlePromotionResult AttachSignedInInstallClaims(
        ReleaseBundlePromotionResult result,
        ReleaseUploadTicketClaims claims)
    {
        if (result.PromotedArtifactIds.Count == 0)
        {
            return result with { SignedInInstallClaims = Array.Empty<ReleasePromotionInstallClaim>() };
        }

        var manifest = _releaseManifestService.LoadManifest();
        var installUrlByArtifactId = result.PromotedArtifactIds
            .Zip(result.InstallDispatchUrls, static (artifactId, installUrl) => new KeyValuePair<string, string>(artifactId, installUrl))
            .ToDictionary(static pair => pair.Key, static pair => pair.Value, StringComparer.OrdinalIgnoreCase);
        var user = _accounts.EnsureUser(claims.SubjectId, claims.DisplayName, claims.Email);
        List<ReleasePromotionInstallClaim> issuedClaims = new();
        foreach (string artifactId in result.PromotedArtifactIds)
        {
            var artifact = manifest.Downloads.FirstOrDefault(item => string.Equals(item.Id, artifactId, StringComparison.OrdinalIgnoreCase));
            if (artifact is null)
            {
                continue;
            }

            var dispatch = _installLinking.IssueDownload(manifest, artifact, user.UserId, claims.SubjectId);
            if (dispatch.ClaimTicket is null)
            {
                continue;
            }

            issuedClaims.Add(new ReleasePromotionInstallClaim(
                ArtifactId: artifactId,
                InstallDispatchUrl: installUrlByArtifactId.TryGetValue(artifactId, out string? installUrl)
                    ? installUrl
                    : $"/downloads/install/{Uri.EscapeDataString(artifactId)}",
                ClaimCode: dispatch.ClaimTicket.ClaimCode,
                ClaimCodeExpiresAtUtc: dispatch.ClaimTicket.ExpiresAtUtc));
        }

        return result with { SignedInInstallClaims = issuedClaims };
    }

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.UTF8.GetBytes(left);
        byte[] rightBytes = Encoding.UTF8.GetBytes(right);
        return CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }

    private sealed record ReleaseBundleAuthorizationContext(ReleaseUploadTicketClaims? UploadTicketClaims);
}
