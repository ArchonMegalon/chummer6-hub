using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class InternalRunsiteOrientationController : ControllerBase
{
    private readonly RunsiteOrientationRequestComposerService _composer;
    private readonly RunsiteOrientationArtifactRequestBridgeService _artifactRequestBridge;
    private readonly HorizonArtifactRequestService _artifactRequests;
    private readonly IConfiguration _configuration;

    public InternalRunsiteOrientationController(
        RunsiteOrientationRequestComposerService composer,
        RunsiteOrientationArtifactRequestBridgeService artifactRequestBridge,
        HorizonArtifactRequestService artifactRequests,
        IConfiguration configuration)
    {
        _composer = composer;
        _artifactRequestBridge = artifactRequestBridge;
        _artifactRequests = artifactRequests;
        _configuration = configuration;
    }

    [HttpPost("/api/internal/runsite-orientation/requests")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<RunsiteOrientationRequestCompositionResult>(StatusCodes.Status200OK)]
    public ActionResult<RunsiteOrientationRequestCompositionResult> Compose([FromBody] RunsiteOrientationRequestComposeRequest? request)
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
                "Runsite orientation request rejected",
                "runsite orientation request is required.",
                "https://chummer.run/problems/runsite-orientation/missing-request");
        }

        try
        {
            return Ok(_composer.Compose(request));
        }
        catch (InvalidDataException ex)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Runsite orientation request rejected",
                ex.Message,
                "https://chummer.run/problems/runsite-orientation/rejected");
        }
    }

    [HttpPost("/api/internal/runsite-orientation/artifact-requests")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<RunsiteOrientationArtifactRequestBridgeResult>(StatusCodes.Status200OK)]
    [ProducesResponseType<RunsiteOrientationArtifactRequestBridgeResult>(StatusCodes.Status400BadRequest)]
    [ProducesResponseType<RunsiteOrientationArtifactRequestBridgeResult>(StatusCodes.Status429TooManyRequests)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public ActionResult<RunsiteOrientationArtifactRequestBridgeResult> ComposeArtifactRequest([FromBody] RunsiteOrientationArtifactRequestBridgeRequest? request)
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
                "Runsite orientation artifact request rejected",
                "runsite orientation artifact request is required.",
                "https://chummer.run/problems/runsite-orientation/missing-artifact-request");
        }

        try
        {
            RunsiteOrientationArtifactRequestBridgePayload payload = _artifactRequestBridge.Compose(request);
            HorizonArtifactRequestReceipt receipt = _artifactRequests.BuildRequest(payload.ArtifactRequest, consumeQuota: payload.ConsumeQuota);
            RunsiteOrientationArtifactRequestBridgeResult result = new(payload.OrientationRequest, receipt);
            if (string.Equals(receipt.Status, "accepted", StringComparison.OrdinalIgnoreCase))
            {
                return Ok(result);
            }

            return receipt.BlockedReasons.Contains("artifact allowance", StringComparer.OrdinalIgnoreCase)
                ? StatusCode(StatusCodes.Status429TooManyRequests, result)
                : StatusCode(StatusCodes.Status400BadRequest, result);
        }
        catch (InvalidDataException ex)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Runsite orientation artifact request rejected",
                ex.Message,
                "https://chummer.run/problems/runsite-orientation/artifact-request-rejected");
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
                "Runsite orientation authorization required",
                "internal runsite orientation authorization is required.",
                "https://chummer.run/problems/runsite-orientation/auth-required");
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        string expectedToken = (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
        if (!string.IsNullOrWhiteSpace(expectedToken) && FixedTimeEquals(providedToken, expectedToken))
        {
            return null;
        }

        return BuildProblem(
            StatusCodes.Status401Unauthorized,
            "Runsite orientation authorization required",
            "internal runsite orientation authorization is required.",
            "https://chummer.run/problems/runsite-orientation/auth-required");
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
