using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Services.Support;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/support/android-diagnostics")]
public sealed class AndroidDiagnosticsController(AndroidDiagnosticStore store) : ControllerBase
{
    [HttpPost]
    // The pre-binding Hub guardrail applies the 2 KiB (or lower configured)
    // limit, including chunked requests. Do not override it with an MVC filter.
    public async Task<ActionResult<AndroidDiagnosticReceipt>> Submit(
        [FromBody] AndroidDiagnosticReport report, CancellationToken ct)
    {
        Response.Headers.CacheControl = "no-store";
        if (!store.Enabled) return StatusCode(StatusCodes.Status503ServiceUnavailable);
        try { return Accepted(await store.SubmitAsync(report, ct)); }
        catch (ArgumentException) { return BadRequest(); }
        catch (AndroidDiagnosticConflictException) { return Conflict(); }
        catch (AndroidDiagnosticCapacityException)
        {
            Response.Headers.RetryAfter = "3600";
            return StatusCode(StatusCodes.Status429TooManyRequests);
        }
        catch (Exception error) when (error is IOException or InvalidDataException or UnauthorizedAccessException or System.Text.Json.JsonException)
        { return StatusCode(StatusCodes.Status503ServiceUnavailable); }
    }

    [HttpGet]
    public async Task<ActionResult<AndroidDiagnosticReadback>> Read(CancellationToken ct)
    {
        Response.Headers.CacheControl = "no-store";
        if (!store.Enabled) return StatusCode(StatusCodes.Status503ServiceUnavailable);
        if (!store.AuthorizeReader(Request.Headers.Authorization.ToString())) return Unauthorized();
        try { return Ok(await store.ReadAsync(ct)); }
        catch (Exception error) when (error is IOException or InvalidDataException or UnauthorizedAccessException or System.Text.Json.JsonException)
        { return StatusCode(StatusCodes.Status503ServiceUnavailable); }
    }
}
