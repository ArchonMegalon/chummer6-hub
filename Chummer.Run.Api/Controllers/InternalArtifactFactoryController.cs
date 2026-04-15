using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class InternalArtifactFactoryController : ControllerBase
{
    private readonly ArtifactFactoryOrchestrationService _orchestration;
    private readonly IConfiguration _configuration;

    public InternalArtifactFactoryController(
        ArtifactFactoryOrchestrationService orchestration,
        IConfiguration configuration)
    {
        _orchestration = orchestration;
        _configuration = configuration;
    }

    [HttpPost("/api/internal/artifact-factory/jobs")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<ArtifactFactoryJobLaunchResult>(StatusCodes.Status200OK)]
    public ActionResult<ArtifactFactoryJobLaunchResult> LaunchJob([FromBody] ArtifactFactoryJobLaunchRequest? request)
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
                "Artifact factory job rejected",
                "job request is required.",
                "https://chummer.run/problems/artifact-factory/missing-request");
        }

        try
        {
            return Ok(_orchestration.LaunchJob(request));
        }
        catch (InvalidDataException ex)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Artifact factory job rejected",
                ex.Message,
                "https://chummer.run/problems/artifact-factory/rejected");
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
                "Artifact factory authorization required",
                "internal artifact factory authorization is required.",
                "https://chummer.run/problems/artifact-factory/auth-required");
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        string expectedToken = (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
        if (!string.IsNullOrWhiteSpace(expectedToken) && FixedTimeEquals(providedToken, expectedToken))
        {
            return null;
        }

        return BuildProblem(
            StatusCodes.Status401Unauthorized,
            "Artifact factory authorization required",
            "internal artifact factory authorization is required.",
            "https://chummer.run/problems/artifact-factory/auth-required");
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
