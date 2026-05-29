using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class InternalExecutiveAssistantCredentialsController : ControllerBase
{
    private readonly ExecutiveAssistantCredentialCatalogService _catalog;
    private readonly IConfiguration _configuration;

    public InternalExecutiveAssistantCredentialsController(
        ExecutiveAssistantCredentialCatalogService catalog,
        IConfiguration configuration)
    {
        _catalog = catalog;
        _configuration = configuration;
    }

    [HttpGet("/api/internal/executive-assistant/credentials")]
    [ProducesResponseType<ExecutiveAssistantCredentialCatalogResult>(StatusCodes.Status200OK)]
    public ActionResult<ExecutiveAssistantCredentialCatalogResult> GetCatalog()
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        return Ok(_catalog.GetCatalog());
    }

    private ActionResult? RequireInternalAutomationAuth()
    {
        string header = Request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return BuildProblem(
                StatusCodes.Status401Unauthorized,
                "Executive assistant credential authorization required",
                "internal executive assistant credential authorization is required.",
                "https://chummer.run/problems/executive-assistant/auth-required");
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        string expectedToken = (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
        if (!string.IsNullOrWhiteSpace(expectedToken) && FixedTimeEquals(providedToken, expectedToken))
        {
            return null;
        }

        return BuildProblem(
            StatusCodes.Status401Unauthorized,
            "Executive assistant credential authorization required",
            "internal executive assistant credential authorization is required.",
            "https://chummer.run/problems/executive-assistant/auth-required");
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
