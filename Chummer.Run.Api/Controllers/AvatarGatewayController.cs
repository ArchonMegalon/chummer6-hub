using Chummer.Run.Api.Services.Avatar;
using Chummer.Run.Contracts.Avatar;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Filters;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/internal/avatar/contexts")]
public sealed class AvatarContextAdministrationController(
    IAvatarGatewayService gateway) : ControllerBase
{
    private const int MaximumRequestBytes = 32 * 1024;

    [HttpPost]
    [RequestSizeLimit(MaximumRequestBytes)]
    [ProducesResponseType<AvatarSessionContextProjection>(StatusCodes.Status201Created)]
    [ProducesResponseType<AvatarGatewayErrorEnvelope>(StatusCodes.Status400BadRequest)]
    [ProducesResponseType<AvatarGatewayErrorEnvelope>(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType<AvatarGatewayErrorEnvelope>(StatusCodes.Status503ServiceUnavailable)]
    public ActionResult<AvatarSessionContextProjection> Mint([FromBody] AvatarContextMintRequest? request)
    {
        AvatarGatewayOperationResult<AvatarSessionContextProjection> result = gateway.Mint(request);
        if (!result.Succeeded)
        {
            return AvatarGatewayHttpResult.Error(result.Status);
        }
        return StatusCode(StatusCodes.Status201Created, result.Value);
    }

    [HttpDelete("{contextRef}")]
    [RequestSizeLimit(MaximumRequestBytes)]
    [ProducesResponseType<AvatarContextRevocationReceipt>(StatusCodes.Status200OK)]
    [ProducesResponseType<AvatarGatewayErrorEnvelope>(StatusCodes.Status400BadRequest)]
    [ProducesResponseType<AvatarGatewayErrorEnvelope>(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType<AvatarGatewayErrorEnvelope>(StatusCodes.Status503ServiceUnavailable)]
    public ActionResult<AvatarContextRevocationReceipt> Revoke(
        [FromRoute] string contextRef,
        [FromBody] AvatarContextRevocationRequest? request)
    {
        if (request is null || !StringComparer.Ordinal.Equals(contextRef, request.ContextRef))
        {
            return AvatarGatewayHttpResult.Error(AvatarGatewayCallStatus.InvalidRequest);
        }

        AvatarGatewayOperationResult<AvatarContextRevocationReceipt> result = gateway.Revoke(request);
        return result.Succeeded
            ? Ok(result.Value)
            : AvatarGatewayHttpResult.Error(result.Status);
    }
}

[ApiController]
[Route("api/v1/avatar")]
public sealed class AvatarGatewayController(
    IAvatarGatewayService gateway) : ControllerBase
{
    private const int MaximumRequestBytes = 32 * 1024;

    [HttpPost("context")]
    [RequestSizeLimit(MaximumRequestBytes)]
    [ProducesResponseType<AvatarSessionContextProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType<AvatarGatewayErrorEnvelope>(StatusCodes.Status400BadRequest)]
    [ProducesResponseType<AvatarGatewayErrorEnvelope>(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType<AvatarGatewayErrorEnvelope>(StatusCodes.Status503ServiceUnavailable)]
    public ActionResult<AvatarSessionContextProjection> GetContext([FromBody] AvatarContextRequest? request)
    {
        AvatarGatewayOperationResult<AvatarSessionContextProjection> result = gateway.GetContext(request);
        return result.Succeeded
            ? Ok(result.Value)
            : AvatarGatewayHttpResult.Error(result.Status);
    }

    [HttpPost("rules/resolve")]
    [RequestSizeLimit(MaximumRequestBytes)]
    [ProducesResponseType<AvatarRuleAnswerEnvelope>(StatusCodes.Status200OK)]
    [ProducesResponseType<AvatarGatewayErrorEnvelope>(StatusCodes.Status400BadRequest)]
    [ProducesResponseType<AvatarGatewayErrorEnvelope>(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType<AvatarGatewayErrorEnvelope>(StatusCodes.Status503ServiceUnavailable)]
    public async Task<ActionResult<AvatarRuleAnswerEnvelope>> ResolveRule(
        [FromBody] AvatarRuleQuestionRequest? request,
        CancellationToken cancellationToken)
    {
        AvatarGatewayOperationResult<AvatarRuleAnswerEnvelope> result =
            await gateway.ResolveRuleAsync(request, cancellationToken).ConfigureAwait(false);
        return result.Succeeded
            ? Ok(result.Value)
            : AvatarGatewayHttpResult.Error(result.Status);
    }
}

internal sealed class AvatarGatewayAuthorizationFilter(
    AvatarGatewayCredentialPolicy credentials) : IAsyncAuthorizationFilter, IOrderedFilter
{
    public int Order => int.MinValue;

    public Task OnAuthorizationAsync(AuthorizationFilterContext context)
    {
        HttpRequest request = context.HttpContext.Request;
        bool administration = request.Path.StartsWithSegments(
            "/api/internal/avatar",
            StringComparison.OrdinalIgnoreCase);
        bool provider = request.Path.StartsWithSegments(
            "/api/v1/avatar",
            StringComparison.OrdinalIgnoreCase);
        if (!administration && !provider)
        {
            return Task.CompletedTask;
        }

        AvatarGatewayHttpResult.ApplyPrivateHeaders(context.HttpContext.Response);
        bool ready = administration ? credentials.ContextMintReady : credentials.ProviderReady;
        bool authorized = administration
            ? credentials.IsContextMintAuthorized(request)
            : credentials.IsProviderAuthorized(request);
        if (!ready)
        {
            context.Result = AvatarGatewayHttpResult.Error(AvatarGatewayCallStatus.InvalidState);
        }
        else if (!authorized)
        {
            context.Result = AvatarGatewayHttpResult.AuthenticationError();
        }
        return Task.CompletedTask;
    }
}

internal static class AvatarGatewayHttpResult
{
    public static ObjectResult AuthenticationError()
        => Result(
            StatusCodes.Status401Unauthorized,
            AvatarGatewayStatuses.Forbidden,
            "avatar-service-auth-invalid",
            retryable: false);

    public static ObjectResult Error(AvatarGatewayCallStatus status)
    {
        (int statusCode, string publicStatus, string reason, bool retryable) = status switch
        {
            AvatarGatewayCallStatus.InvalidRequest => (
                StatusCodes.Status400BadRequest,
                AvatarGatewayStatuses.Unresolved,
                "avatar-request-invalid",
                false),
            AvatarGatewayCallStatus.NotFound or AvatarGatewayCallStatus.Expired => (
                StatusCodes.Status410Gone,
                AvatarGatewayStatuses.Stale,
                "avatar-context-unavailable",
                false),
            AvatarGatewayCallStatus.ScenarioMismatch or AvatarGatewayCallStatus.SessionMismatch => (
                StatusCodes.Status403Forbidden,
                AvatarGatewayStatuses.Forbidden,
                "avatar-context-binding-invalid",
                false),
            AvatarGatewayCallStatus.NonceReplay or AvatarGatewayCallStatus.IdempotencyConflict => (
                StatusCodes.Status409Conflict,
                AvatarGatewayStatuses.Conflict,
                "avatar-request-replay-conflict",
                false),
            AvatarGatewayCallStatus.RateLimited => (
                StatusCodes.Status429TooManyRequests,
                AvatarGatewayStatuses.Unavailable,
                "avatar-rate-limit-reached",
                true),
            _ => (
                StatusCodes.Status503ServiceUnavailable,
                AvatarGatewayStatuses.Unavailable,
                "avatar-gateway-unavailable",
                true)
        };
        return Result(statusCode, publicStatus, reason, retryable);
    }

    public static void ApplyPrivateHeaders(HttpResponse response)
    {
        response.Headers.CacheControl = "no-store, max-age=0";
        response.Headers.Pragma = "no-cache";
        response.Headers.Expires = "0";
        response.Headers["Referrer-Policy"] = "no-referrer";
        response.Headers["X-Content-Type-Options"] = "nosniff";
    }

    private static AvatarGatewayErrorEnvelope Envelope(string status, string reason, bool retryable)
        => new(AvatarGatewayContractVersions.ErrorV1, status, reason, retryable);

    private static ObjectResult Result(int statusCode, string status, string reason, bool retryable)
        => new(Envelope(status, reason, retryable)) { StatusCode = statusCode };
}
