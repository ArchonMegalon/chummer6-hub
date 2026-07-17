using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.AI.Security;

public sealed class AiMutationAuthorizationMiddleware
{
    public const string PrimaryTokenConfigurationKey = "CHUMMER_AI_INTERNAL_API_TOKEN";
    public const string FallbackTokenConfigurationKey = "FLEET_INTERNAL_API_TOKEN";
    internal static readonly object AuthorizationMarker = new();

    private readonly RequestDelegate _next;

    public AiMutationAuthorizationMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(HttpContext context, IConfiguration configuration)
    {
        if (IsAnonymousRequest(context.Request))
        {
            await _next(context);
            return;
        }

        string expectedToken = ResolveExpectedToken(configuration);
        if (string.IsNullOrWhiteSpace(expectedToken))
        {
            await WriteProblemAsync(
                context,
                StatusCodes.Status503ServiceUnavailable,
                "AI internal authorization is unavailable.",
                "The AI service has no internal authorization token configured.",
                "https://chummer.run/problems/ai-internal-auth-unavailable");
            return;
        }

        if (!TryReadBearerToken(context.Request, out string suppliedToken)
            || !TokensMatch(expectedToken, suppliedToken))
        {
            context.Response.Headers.WWWAuthenticate = "Bearer";
            await WriteProblemAsync(
                context,
                StatusCodes.Status401Unauthorized,
                "AI internal authorization failed.",
                "A valid internal bearer token is required for this AI service route.",
                "https://chummer.run/problems/ai-internal-auth-required");
            return;
        }

        context.Items[AuthorizationMarker] = true;
        await _next(context);
    }

    private static bool IsAnonymousRequest(HttpRequest request)
    {
        if (HttpMethods.IsOptions(request.Method))
        {
            return true;
        }

        if (!HttpMethods.IsGet(request.Method) && !HttpMethods.IsHead(request.Method))
        {
            return false;
        }

        string path = NormalizePath(request.Path.Value);
        return string.Equals(path, AiPublicEndpoints.HealthPath, StringComparison.OrdinalIgnoreCase)
               || string.Equals(path, AiPublicEndpoints.CapabilitiesPath, StringComparison.OrdinalIgnoreCase);
    }

    private static string NormalizePath(string? path)
    {
        string normalized = string.IsNullOrWhiteSpace(path) ? "/" : path;
        return normalized.Length > 1 ? normalized.TrimEnd('/') : normalized;
    }

    private static string ResolveExpectedToken(IConfiguration configuration)
    {
        string primaryToken = (configuration[PrimaryTokenConfigurationKey] ?? string.Empty).Trim();
        return primaryToken.Length > 0
            ? primaryToken
            : (configuration[FallbackTokenConfigurationKey] ?? string.Empty).Trim();
    }

    private static bool TryReadBearerToken(HttpRequest request, out string token)
    {
        token = string.Empty;
        if (!AuthenticationHeaderValue.TryParse(request.Headers.Authorization.ToString(), out AuthenticationHeaderValue? authorization)
            || !string.Equals(authorization.Scheme, "Bearer", StringComparison.OrdinalIgnoreCase)
            || string.IsNullOrWhiteSpace(authorization.Parameter))
        {
            return false;
        }

        token = authorization.Parameter.Trim();
        return token.Length > 0;
    }

    private static bool TokensMatch(string expectedToken, string suppliedToken)
    {
        byte[] expectedHash = SHA256.HashData(Encoding.UTF8.GetBytes(expectedToken));
        byte[] suppliedHash = SHA256.HashData(Encoding.UTF8.GetBytes(suppliedToken));
        return CryptographicOperations.FixedTimeEquals(expectedHash, suppliedHash);
    }

    private static async Task WriteProblemAsync(
        HttpContext context,
        int statusCode,
        string title,
        string detail,
        string type)
    {
        context.Response.StatusCode = statusCode;
        await context.Response.WriteAsJsonAsync(
            new ProblemDetails
            {
                Status = statusCode,
                Title = title,
                Detail = detail,
                Type = type
            },
            options: null,
            contentType: "application/problem+json; charset=utf-8",
            cancellationToken: context.RequestAborted);
    }
}
