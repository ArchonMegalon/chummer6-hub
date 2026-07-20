using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/antiforgery")]
public sealed class AntiforgeryController : ControllerBase
{
    private readonly IAntiforgery _antiforgery;
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;

    public AntiforgeryController(
        IAntiforgery antiforgery,
        AccountService accounts,
        HubIdentityClient identity)
    {
        _antiforgery = antiforgery;
        _accounts = accounts;
        _identity = identity;
    }

    [HttpGet]
    [IgnoreAntiforgeryToken]
    [ResponseCache(NoStore = true, Location = ResponseCacheLocation.None)]
    [ProducesResponseType(typeof(AntiforgeryTokenProjection), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public async Task<ActionResult<AntiforgeryTokenProjection>> Get(CancellationToken cancellationToken)
    {
        try
        {
            AuthenticatedHubSubject subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            AntiforgeryTokenSet tokens = _antiforgery.GetAndStoreTokens(HttpContext);
            if (string.IsNullOrWhiteSpace(tokens.RequestToken)
                || string.IsNullOrWhiteSpace(tokens.HeaderName))
            {
                return Problem(
                    statusCode: StatusCodes.Status503ServiceUnavailable,
                    detail: "Antiforgery token issuance is unavailable.");
            }

            ApplyPrivateHeaders();
            return Ok(new AntiforgeryTokenProjection(tokens.RequestToken, tokens.HeaderName));
        }
        catch (HubRequestAuthException exception)
        {
            ApplyPrivateHeaders();
            return Problem(statusCode: exception.StatusCode, detail: exception.Message);
        }
    }

    private void ApplyPrivateHeaders()
    {
        Response.Headers.CacheControl = "private, no-store, no-cache, max-age=0";
        Response.Headers.Pragma = "no-cache";
        Response.Headers["Referrer-Policy"] = "no-referrer";
        Response.Headers["X-Content-Type-Options"] = "nosniff";
    }
}
