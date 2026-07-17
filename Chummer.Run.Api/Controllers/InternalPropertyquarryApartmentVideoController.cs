using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class InternalPropertyquarryApartmentVideoController : ControllerBase
{
    private readonly PropertyquarryApartmentVideoArtifactRequestBridgeService _bridge;
    private readonly HorizonArtifactRequestService _artifactRequests;
    private readonly IConfiguration _configuration;

    public InternalPropertyquarryApartmentVideoController(
        PropertyquarryApartmentVideoArtifactRequestBridgeService bridge,
        HorizonArtifactRequestService artifactRequests,
        IConfiguration configuration)
    {
        _bridge = bridge;
        _artifactRequests = artifactRequests;
        _configuration = configuration;
    }

    [HttpPost("/api/internal/propertyquarry/apartment-videos/requests")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<PropertyquarryApartmentVideoArtifactRequestBridgePayload>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<PropertyquarryApartmentVideoArtifactRequestBridgePayload> Compose([FromBody] PropertyquarryApartmentVideoArtifactRequestBridgeRequest? request)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        if (request is null)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "PROPERTYQUARRY apartment video request rejected",
                "propertyquarry apartment video request is required.",
                "https://chummer.run/problems/propertyquarry/apartment-video/missing-request");
        }

        try
        {
            return Ok(_bridge.Compose(request));
        }
        catch (KeyNotFoundException ex)
        {
            return Problem(statusCode: StatusCodes.Status404NotFound, detail: ex.Message);
        }
    }

    [HttpPost("/api/internal/propertyquarry/apartment-videos/artifact-requests")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<PropertyquarryApartmentVideoArtifactRequestBridgeResult>(StatusCodes.Status200OK)]
    [ProducesResponseType<PropertyquarryApartmentVideoArtifactRequestBridgeResult>(StatusCodes.Status400BadRequest)]
    [ProducesResponseType<PropertyquarryApartmentVideoArtifactRequestBridgeResult>(StatusCodes.Status429TooManyRequests)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public ActionResult<PropertyquarryApartmentVideoArtifactRequestBridgeResult> ComposeArtifactRequest([FromBody] PropertyquarryApartmentVideoArtifactRequestBridgeRequest? request)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        if (request is null)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "PROPERTYQUARRY apartment video artifact request rejected",
                "propertyquarry apartment video artifact request is required.",
                "https://chummer.run/problems/propertyquarry/apartment-video/missing-artifact-request");
        }

        try
        {
            PropertyquarryApartmentVideoArtifactRequestBridgePayload payload = _bridge.Compose(request);
            HorizonArtifactRequestReceipt receipt = _artifactRequests.BuildRequest(payload.ArtifactRequest, consumeQuota: payload.ConsumeQuota);
            PropertyquarryApartmentVideoArtifactRequestBridgeResult result = new(payload, receipt);
            if (string.Equals(receipt.Status, "accepted", StringComparison.OrdinalIgnoreCase))
            {
                return Ok(result);
            }

            return receipt.BlockedReasons.Contains("artifact allowance", StringComparer.OrdinalIgnoreCase)
                ? StatusCode(StatusCodes.Status429TooManyRequests, result)
                : StatusCode(StatusCodes.Status400BadRequest, result);
        }
        catch (BrilliantDirectoriesBillingUnavailableException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
        catch (KeyNotFoundException ex)
        {
            return Problem(statusCode: StatusCodes.Status404NotFound, detail: ex.Message);
        }
    }

    private ActionResult? RequireInternalAutomationAuth()
    {
        string header = Request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return BuildProblem(
                StatusCodes.Status401Unauthorized,
                "PROPERTYQUARRY apartment video authorization required",
                "internal propertyquarry apartment video authorization is required.",
                "https://chummer.run/problems/propertyquarry/apartment-video/auth-required");
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        string expectedToken = (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
        if (!string.IsNullOrWhiteSpace(expectedToken) && FixedTimeEquals(providedToken, expectedToken))
        {
            return null;
        }

        return BuildProblem(
            StatusCodes.Status401Unauthorized,
            "PROPERTYQUARRY apartment video authorization required",
            "internal propertyquarry apartment video authorization is required.",
            "https://chummer.run/problems/propertyquarry/apartment-video/auth-required");
    }

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.UTF8.GetBytes(left);
        byte[] rightBytes = Encoding.UTF8.GetBytes(right);
        return CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }

    private ObjectResult BuildProblem(
        int statusCode,
        string title,
        string detail,
        string type)
    {
        return Problem(
            detail: detail,
            statusCode: statusCode,
            title: title,
            type: type,
            instance: $"{Request.Path}#{Request.HttpContext.TraceIdentifier}");
    }
}
