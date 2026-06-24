using Chummer.Run.Contracts.Identity;
using Chummer.Run.Identity.Services;
using Microsoft.AspNetCore.Mvc;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Chummer.Run.Identity.Controllers;

[ApiController]
[Route("api/v1/identity")]
public sealed class IdentityController : ControllerBase
{
    private readonly IIdentityAccessService _identity;
    private readonly IIdentityEmailDeliveryService _emailDelivery;
    private readonly IConfiguration _configuration;

    public IdentityController(IIdentityAccessService identity, IIdentityEmailDeliveryService emailDelivery, IConfiguration configuration)
    {
        _identity = identity;
        _emailDelivery = emailDelivery;
        _configuration = configuration;
    }

    [HttpPost("sessions")]
    [ProducesResponseType<IdentitySessionIssueResponse>(StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<IdentitySessionIssueResponse> IssueSession([FromBody] IdentitySessionIssueRequest? request)
    {
        if (!IsAdminRouteAuthorized())
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: "identity session issuance is reserved for internal or admin callers.");
        }

        if (request is null || string.IsNullOrWhiteSpace(request.SubjectId))
        {
            return BadRequest("subjectId is required.");
        }

        var issued = _identity.IssueSession(request);
        return CreatedAtAction(nameof(GetSubject), new { subjectId = issued.SubjectId }, issued);
    }

    [HttpPost("email/start")]
    [ProducesResponseType<EmailAuthStartResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<EmailAuthStartResponse> StartEmailEntry([FromBody] EmailAuthStartRequest? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.Email))
        {
            return BadRequest("email is required.");
        }

        return Ok(_identity.StartEmailEntry(request));
    }

    [HttpGet("email/delivery-status")]
    [ProducesResponseType<IdentityEmailDeliveryStatusResponse>(StatusCodes.Status200OK)]
    public ActionResult<IdentityEmailDeliveryStatusResponse> GetEmailDeliveryStatus()
        => Ok(_emailDelivery.GetStatus());

    [HttpPost("email/providers/emailit/webhook")]
    [ProducesResponseType<IdentityEmailWebhookAckResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public ActionResult<IdentityEmailWebhookAckResponse> ReceiveEmailitWebhook([FromBody] JsonElement payload)
    {
        var authorizationFailure = ValidateEmailitWebhookAuthorization();
        if (authorizationFailure is not null)
        {
            return authorizationFailure;
        }

        return Ok(_emailDelivery.RecordEmailitWebhook(payload));
    }

    [HttpPost("email/complete")]
    [ProducesResponseType<IdentitySessionIssueResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<IdentitySessionIssueResponse> CompleteEmailEntry([FromBody] EmailAuthCompleteRequest? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.TicketId))
        {
            return BadRequest("ticketId is required.");
        }

        try
        {
            return Ok(_identity.CompleteEmailEntry(request));
        }
        catch (Exception ex) when (ex is KeyNotFoundException or ArgumentException)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpGet("subjects/{subjectId}")]
    [ProducesResponseType<IdentitySubjectResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<IdentitySubjectResponse> GetSubject([FromRoute] string subjectId)
    {
        if (string.IsNullOrWhiteSpace(subjectId))
        {
            return BadRequest("subjectId is required.");
        }

        var subject = _identity.GetSubject(subjectId);
        return subject is null ? NotFound() : Ok(subject);
    }

    [HttpPut("subjects/{subjectId}/roles")]
    [ProducesResponseType<IdentitySubjectResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<IdentitySubjectResponse> SetRoles(
        [FromRoute] string subjectId,
        [FromBody] IdentityRoleSetRequest? request)
    {
        if (!IsAdminRouteAuthorized())
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: "identity role mutation is reserved for internal or admin callers.");
        }

        if (string.IsNullOrWhiteSpace(subjectId))
        {
            return BadRequest("subjectId is required.");
        }

        if (request is null || request.Roles is null)
        {
            return BadRequest("roles are required.");
        }

        return Ok(_identity.SetRoles(subjectId, request));
    }

    [HttpPost("sessions/revoke")]
    [ProducesResponseType<IdentitySessionRevokeResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<IdentitySessionRevokeResponse> RevokeSession([FromBody] IdentitySessionRevokeRequest? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.AccessToken))
        {
            return BadRequest("accessToken is required.");
        }

        return Ok(_identity.RevokeSession(request));
    }

    [HttpPost("introspect")]
    [ProducesResponseType<IdentityIntrospectionResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<IdentityIntrospectionResponse> Introspect([FromBody] IdentityIntrospectionRequest? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.AccessToken))
        {
            return BadRequest("accessToken is required.");
        }

        return Ok(_identity.Introspect(request));
    }

    private bool IsAdminRouteAuthorized()
    {
        var configuredKey = _configuration["IDENTITY_ADMIN_KEY"];
        if (string.IsNullOrWhiteSpace(configuredKey))
        {
            return false;
        }

        if (!Request.Headers.TryGetValue("X-Identity-Admin-Key", out var supplied))
        {
            return false;
        }

        return string.Equals(supplied.ToString(), configuredKey, StringComparison.Ordinal);
    }

    private ObjectResult? ValidateEmailitWebhookAuthorization()
    {
        var configuredSecret = _configuration["IDENTITY_EMAILIT_WEBHOOK_SECRET"]?.Trim();
        if (string.IsNullOrWhiteSpace(configuredSecret))
        {
            return ResolveBool(_configuration["IDENTITY_UNSAFE_ALLOW_UNSIGNED_EMAILIT_WEBHOOKS"], defaultValue: false)
                ? null
                : Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "emailit webhook secret is not configured.");
        }

        var suppliedSecret = Request.Headers["X-Emailit-Webhook-Secret"].ToString();
        if (string.IsNullOrWhiteSpace(suppliedSecret) || !FixedTimeEquals(suppliedSecret.Trim(), configuredSecret))
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: "emailit webhook secret mismatch.");
        }

        return null;
    }

    private static bool FixedTimeEquals(string supplied, string expected)
    {
        byte[] suppliedBytes = Encoding.UTF8.GetBytes(supplied);
        byte[] expectedBytes = Encoding.UTF8.GetBytes(expected);
        return suppliedBytes.Length == expectedBytes.Length
               && CryptographicOperations.FixedTimeEquals(suppliedBytes, expectedBytes);
    }

    private static bool ResolveBool(string? value, bool defaultValue)
        => bool.TryParse(value, out var parsed) ? parsed : defaultValue;
}
