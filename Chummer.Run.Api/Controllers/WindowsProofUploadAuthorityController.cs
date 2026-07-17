using System.Text.Encodings.Web;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[Controller]
public sealed class WindowsProofUploadAuthorityController : Controller
{
    private readonly HubIdentityClient _identity;
    private readonly WindowsProofUploadTicketService _tickets;
    private readonly WindowsProofUploadOptions _options;
    private readonly IAntiforgery _antiforgery;
    private readonly ILogger<WindowsProofUploadAuthorityController> _logger;

    public WindowsProofUploadAuthorityController(
        HubIdentityClient identity,
        WindowsProofUploadTicketService tickets,
        WindowsProofUploadOptions options,
        IAntiforgery antiforgery,
        ILogger<WindowsProofUploadAuthorityController> logger)
    {
        _identity = identity ?? throw new ArgumentNullException(nameof(identity));
        _tickets = tickets ?? throw new ArgumentNullException(nameof(tickets));
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _antiforgery = antiforgery ?? throw new ArgumentNullException(nameof(antiforgery));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    [HttpGet("/downloads/proof/windows/upload")]
    [Produces("text/html")]
    [ResponseCache(NoStore = true, Location = ResponseCacheLocation.None)]
    public async Task<IActionResult> UploadHandoff(CancellationToken cancellationToken)
    {
        ApplyPrivateHeaders(Response.Headers);
        IActionResult? unavailable = RequireLaneEnabled();
        if (unavailable is not null)
        {
            return unavailable;
        }

        try
        {
            AuthenticatedHubSubject subject = await _identity.RequireFreshSubjectAsync(Request, cancellationToken);
            if (!ReleaseUploadAccessPolicy.CanAccess(subject))
            {
                return NotFound();
            }

            AntiforgeryTokenSet tokens = _antiforgery.GetAndStoreTokens(HttpContext);
            string fieldName = HtmlEncoder.Default.Encode(tokens.FormFieldName);
            string token = HtmlEncoder.Default.Encode(tokens.RequestToken ?? string.Empty);
            const string action = "/downloads/proof/windows/upload-ticket";
            string html = $$"""
                <!doctype html>
                <html lang="en">
                <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Windows proof upload</title></head>
                <body>
                  <main>
                    <h1>Windows proof upload</h1>
                    <p>This mints a short-lived credential for the Cloudflare-gated, proof-only Windows lane. It cannot publish the canonical release shelf.</p>
                    <form method="post" action="{{action}}">
                      <input type="hidden" name="{{fieldName}}" value="{{token}}">
                      <button type="submit">Mint proof upload credential</button>
                    </form>
                  </main>
                </body>
                </html>
                """;
            return Content(html, "text/html; charset=utf-8");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(Request.Path)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(
                "Windows proof upload handoff could not confirm signed-in authority ({StatusCode}).",
                ex.StatusCode);
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("/downloads/proof/windows/upload-ticket")]
    [Produces("application/json", "application/problem+json")]
    [ResponseCache(NoStore = true, Location = ResponseCacheLocation.None)]
    [ValidateAntiForgeryToken]
    public async Task<IActionResult> IssueUploadTicket(CancellationToken cancellationToken)
    {
        ApplyPrivateHeaders(Response.Headers);
        IActionResult? unavailable = RequireLaneEnabled();
        if (unavailable is not null)
        {
            return unavailable;
        }

        try
        {
            AuthenticatedHubSubject subject = await _identity.RequireFreshSubjectAsync(Request, cancellationToken);
            if (!ReleaseUploadAccessPolicy.CanAccess(subject))
            {
                return NotFound();
            }

            WindowsProofUploadTicketIssueResult issued = _tickets.Issue(subject);
            return Ok(new
            {
                ticket = issued.Ticket,
                scope = WindowsProofUploadTicketService.TicketScope,
                expiresAtUtc = issued.Claims.ExpiresAtUtc,
                createSessionUrl = "/api/internal/windows-proof/upload-sessions",
                credentialTransport = "authorization_bearer_header_only",
                releaseEffect = "windows_proof_only"
            });
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Problem(
                statusCode: StatusCodes.Status401Unauthorized,
                detail: "Sign in again before minting a Windows proof upload credential.");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(
                "Windows proof upload ticket could not confirm signed-in authority ({StatusCode}).",
                ex.StatusCode);
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    private IActionResult? RequireLaneEnabled()
        => _options.Enabled && _options.CfAccessGated
            ? null
            : Problem(
                statusCode: StatusCodes.Status503ServiceUnavailable,
                title: "Windows proof upload lane disabled",
                detail: "Explicit upload enablement and Cloudflare Access gating are required.");

    private static void ApplyPrivateHeaders(IHeaderDictionary headers)
    {
        headers["Cache-Control"] = "private, no-store, max-age=0";
        headers["CDN-Cache-Control"] = "no-store, max-age=0";
        headers["Cloudflare-CDN-Cache-Control"] = "no-store, max-age=0";
        headers["Pragma"] = "no-cache";
        headers["Expires"] = "0";
        headers["Referrer-Policy"] = "no-referrer";
    }
}
