using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class InternalRunsiteOrientationController : ControllerBase
{
    private readonly RunsiteOrientationRequestComposerService _composer;
    private readonly IConfiguration _configuration;

    public InternalRunsiteOrientationController(
        RunsiteOrientationRequestComposerService composer,
        IConfiguration configuration)
    {
        _composer = composer;
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
