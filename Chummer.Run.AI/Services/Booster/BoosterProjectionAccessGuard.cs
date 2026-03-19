using Microsoft.AspNetCore.Http;

namespace Chummer.Run.AI.Services.Booster;

public sealed class BoosterProjectionAccessGuard
{
    private readonly IConfiguration _configuration;

    public BoosterProjectionAccessGuard(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public void Require(HttpRequest request)
    {
        var configured = Normalize(_configuration["BOOSTER_PROJECTION_READ_TOKEN"])
            ?? Normalize(_configuration["FLEET_RECEIPT_SIGNING_SECRET"]);
        if (configured is null)
        {
            throw new BoosterProjectionAccessException(StatusCodes.Status503ServiceUnavailable, "booster projection read auth is not configured.");
        }

        var authHeader = request.Headers.Authorization.ToString();
        var bearer = authHeader.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase)
            ? Normalize(authHeader["Bearer ".Length..])
            : null;
        var headerToken = Normalize(request.Headers["X-Booster-Projection-Token"].ToString());
        var candidate = bearer ?? headerToken;
        if (candidate is null || !string.Equals(candidate, configured, StringComparison.Ordinal))
        {
            throw new BoosterProjectionAccessException(StatusCodes.Status401Unauthorized, "booster projection read auth failed.");
        }
    }

    private static string? Normalize(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}

public sealed class BoosterProjectionAccessException : Exception
{
    public BoosterProjectionAccessException(int statusCode, string message)
        : base(message)
    {
        StatusCode = statusCode;
    }

    public int StatusCode { get; }
}
